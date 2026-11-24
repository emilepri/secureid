"""Liste de révocation signée par l'émetteur (fichier .sid).

Le vérificateur fonctionne hors ligne : on lui transmet ce fichier (clé USB,
partage réseau...). Comme il est signé, personne ne peut retirer une carte de
la liste sans que la signature devienne invalide.

Format : SIDRL1.<contenu JSON en base64url>.<signature en base64url>
Contenu : {"kid": ..., "emis": "AAAA-MM-JJTHH:MM:SS+00:00", "revoquees": ["STU-2026-002", ...]}
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core import crypto
from core.sid_token import _b64d, _b64e, canonical

PREFIX = "SIDRL1"


class RevocationListError(ValueError):
    pass


@dataclass(frozen=True)
class RevocationList:
    kid: str
    emis: str
    revoquees: frozenset[str]

    def __contains__(self, card_id: str) -> bool:
        return card_id in self.revoquees


def build(card_ids: list[str], private_key: Ed25519PrivateKey, kid: str) -> str:
    body = canonical({"kid": kid, "emis": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "revoquees": sorted(set(card_ids))})
    return f"{PREFIX}.{_b64e(body)}.{_b64e(crypto.sign(private_key, body))}"


def write(path: str | Path, card_ids: list[str], private_key: Ed25519PrivateKey, kid: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(card_ids, private_key, kid), encoding="ascii")
    return path


def parse(text: str, public_keys: dict[str, Ed25519PublicKey]) -> RevocationList:
    parts = text.strip().split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise RevocationListError("Fichier de révocation non reconnu.")
    try:
        body, sig = _b64d(parts[1]), _b64d(parts[2])
        data = json.loads(body)
    except ValueError as exc:
        raise RevocationListError("Fichier de révocation corrompu.") from exc
    key = public_keys.get(data.get("kid"))
    if key is None or not crypto.verify(key, sig, body):
        raise RevocationListError("Signature de la liste de révocation invalide : fichier refusé.")
    return RevocationList(data["kid"], data["emis"], frozenset(data["revoquees"]))


def load(path: str | Path, public_keys: dict[str, Ed25519PublicKey]) -> RevocationList:
    return parse(Path(path).read_text(encoding="ascii"), public_keys)
