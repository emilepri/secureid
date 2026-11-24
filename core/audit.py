"""Journal d'audit chaîné par hachage.

Chaque entrée contient le SHA-256 de l'entrée précédente. Modifier, supprimer
ou insérer une ligne à la main casse la chaîne, ce que verify_chain détecte.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AuditLog

GENESIS = "0" * 64  # hash_precedent de la toute première entrée


@dataclass
class ChainReport:
    ok: bool
    entries: int
    first_bad_id: int | None = None
    reason: str = ""


def _compute_hash(prev_hash: str, horodatage: str, operateur: str, action: str, cible: str, details: str) -> str:
    content = json.dumps(
        [prev_hash, horodatage, operateur, action, cible, details],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _last_entry(session: Session) -> AuditLog | None:
    return session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()


def add_entry(session: Session, operateur: str, action: str, cible: str, details: str = "") -> AuditLog:
    """Ajoute une entrée au journal (sans commit : l'appelant valide sa transaction)."""
    last = _last_entry(session)
    prev_hash = last.hash if last else GENESIS
    horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = AuditLog(
        horodatage=horodatage,
        operateur=operateur,
        action=action,
        cible=cible,
        details=details,
        hash_precedent=prev_hash,
        hash=_compute_hash(prev_hash, horodatage, operateur, action, cible, details),
    )
    session.add(entry)
    session.flush()
    return entry


def verify_chain(session: Session) -> ChainReport:
    entries = session.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    expected_prev = GENESIS
    for e in entries:
        if e.hash_precedent != expected_prev:
            return ChainReport(False, len(entries), e.id, "Chaînage rompu : une entrée a été supprimée ou insérée.")
        recomputed = _compute_hash(e.hash_precedent, e.horodatage, e.operateur, e.action, e.cible, e.details)
        if recomputed != e.hash:
            return ChainReport(False, len(entries), e.id, "Contenu modifié après écriture.")
        expected_prev = e.hash
    return ChainReport(True, len(entries))
