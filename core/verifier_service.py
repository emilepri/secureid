"""Vérification d'une carte, hors ligne : signature, expiration, révocation, photo.

Dossier de confiance du vérificateur (par défaut « verif/ ») :
    verif/cles/<kid>_public.pem   clés publiques des émetteurs reconnus
    verif/revocations.sid         liste de révocation signée (facultative mais recommandée)
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from PIL import Image

from core import crypto, photo, revocation, sid_token
from core.qr_reader import decode_qr

REVOQUEE = "REVOQUEE"

VERDICTS = {
    sid_token.AUTHENTIQUE: ("Carte authentique", "#15803d"),
    REVOQUEE: ("Carte révoquée", "#c2410c"),
    sid_token.EXPIREE: ("Carte expirée", "#c2410c"),
    sid_token.FALSIFIEE: ("Carte falsifiée", "#b91c1c"),
    sid_token.INVALIDE: ("QR illisible ou inconnu", "#475569"),
}


@dataclass
class Verdict:
    status: str
    reason: str
    payload: dict = field(default_factory=dict)
    photo_ref: Image.Image | None = None
    photo_conforme: bool | None = None  # None : pas de photo de référence disponible
    at: datetime = field(default_factory=datetime.now)

    @property
    def title(self) -> str:
        return VERDICTS[self.status][0]

    @property
    def color(self) -> str:
        return VERDICTS[self.status][1]

    @property
    def ok(self) -> bool:
        return self.status == sid_token.AUTHENTIQUE


class VerifierService:
    def __init__(self, public_keys: dict[str, Ed25519PublicKey],
                 revoked: revocation.RevocationList | None = None, photos_dir: str | Path | None = None):
        self.public_keys = public_keys
        self.revoked = revoked
        self.photos_dir = Path(photos_dir) if photos_dir else None

    @classmethod
    def from_folder(cls, folder: str | Path = "verif", photos_dir: str | Path | None = None
                    ) -> tuple["VerifierService", list[str]]:
        """Charge le dossier de confiance. Retourne aussi les avertissements à afficher."""
        folder = Path(folder)
        warnings = []
        keys = {}
        for pem in sorted((folder / "cles").glob("*_public.pem")):
            try:
                keys[pem.name.removesuffix("_public.pem")] = crypto.load_public_key(pem)
            except (ValueError, TypeError):
                warnings.append(f"Clé ignorée (illisible) : {pem.name}")
        if not keys:
            warnings.append(f"Aucune clé publique dans {folder / 'cles'} : aucune carte ne pourra être validée.")
        revoked = None
        rl_path = folder / "revocations.sid"
        if rl_path.exists():
            try:
                revoked = revocation.load(rl_path, keys)
            except revocation.RevocationListError as exc:
                warnings.append(str(exc))
        else:
            warnings.append("Pas de liste de révocation : les cartes révoquées ne seront pas détectées.")
        return cls(keys, revoked, photos_dir), warnings

    # ------------------------------------------------------------
    def verify_token(self, token: str, today: date | None = None) -> Verdict:
        res = sid_token.verify_token(token, self.public_keys, today)
        verdict = Verdict(res.status, res.reason, res.payload)
        # Révocation : seulement pour une carte dont la signature est valide
        if res.status in (sid_token.AUTHENTIQUE, sid_token.EXPIREE) and self.revoked \
                and res.payload.get("id") in self.revoked:
            verdict.status, verdict.reason = REVOQUEE, "Cette carte figure sur la liste de révocation signée."
        if res.status != sid_token.FALSIFIEE and res.status != sid_token.INVALIDE:
            self._check_photo(verdict)
        return verdict

    def verify_image(self, image, today: date | None = None) -> Verdict:
        token = decode_qr(image)
        if token is None:
            return Verdict(sid_token.INVALIDE, "Aucun QR code SecureID détecté sur l'image.")
        return self.verify_token(token, today)

    def _check_photo(self, verdict: Verdict) -> None:
        """Si la photo de référence est disponible (même poste que l'émission), on compare son empreinte."""
        card_id = verdict.payload.get("id")
        if not (self.photos_dir and card_id):
            return
        path = self.photos_dir / f"{card_id}.png"
        if not path.exists():
            return
        ref = Image.open(path).convert("RGB")
        verdict.photo_ref = ref
        try:
            verdict.photo_conforme = photo.fingerprint(ref) == verdict.payload.get("ph")
        except ValueError:
            verdict.photo_conforme = False

    @property
    def revocation_info(self) -> str:
        if not self.revoked:
            return "aucune liste de révocation"
        emis = datetime.fromisoformat(self.revoked.emis).astimezone().strftime("%d/%m/%Y %H:%M")
        return f"liste de révocation du {emis} ({len(self.revoked.revoquees)} carte(s))"
