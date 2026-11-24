"""Logique d'émission des cartes, indépendante de l'interface graphique.

L'interface PySide6 ne fait qu'appeler ce service : on peut donc tout tester
sans fenêtre, et réutiliser le service plus tard dans une application web.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PIL import Image
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from core import audit, photo, revocation, sid_token
from core.pdf_export import export_card_pdf
from core.render import PROFILES, CardData
from core.templates import DEFAULT_TEMPLATE, render_card
from db.models import Card, Holder, Revocation, SigningKey

ID_PREFIX = {"ecole": "STU", "entreprise": "EMP"}
NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' -]{1,60}$")


class ValidationError(ValueError):
    """Données du formulaire invalides ; le message est affichable tel quel."""


@dataclass
class CardRequest:
    """Ce que l'opérateur saisit dans le formulaire."""

    profil: str
    nom: str
    prenom: str
    naiss: date
    role: str
    validite_mois: int = 12
    fonction: str = ""
    service: str = ""
    modele: str = DEFAULT_TEMPLATE
    photo_source: str | Path | Image.Image | None = None

    errors: list[str] = field(default_factory=list, init=False, repr=False)


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    day = min(d.day, [31, 29 if (d.year + y) % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m])
    return date(d.year + y, m + 1, day)


def validate(req: CardRequest, today: date | None = None) -> None:
    today = today or date.today()
    errors = []
    if req.profil not in PROFILES:
        errors.append("Profil inconnu.")
    for label, value in (("Nom", req.nom), ("Prénom", req.prenom)):
        if not value.strip():
            errors.append(f"{label} obligatoire.")
        elif not NAME_RE.match(value.strip()):
            errors.append(f"{label} : lettres, espaces, tirets et apostrophes uniquement.")
    age = (today - req.naiss).days / 365.25
    if not 14 <= age <= 100:
        errors.append("Date de naissance invraisemblable (âge entre 14 et 100 ans attendu).")
    if not req.role.strip():
        errors.append("Statut obligatoire.")
    if req.profil == "entreprise" and (not req.fonction.strip() or not req.service.strip()):
        errors.append("Fonction et service obligatoires pour une carte entreprise.")
    if not 1 <= req.validite_mois <= 60:
        errors.append("Validité entre 1 et 60 mois.")
    if req.photo_source is None:
        errors.append("Photo obligatoire.")
    if errors:
        raise ValidationError("\n".join(errors))


class IssuerService:
    def __init__(self, session_factory: sessionmaker[Session], private_key: Ed25519PrivateKey,
                 kid: str, operateur: str, data_dir: str | Path = "data", out_dir: str | Path = "sortie"):
        self.Session = session_factory
        self.private_key = private_key
        self.kid = kid
        self.operateur = operateur
        self.photos_dir = Path(data_dir) / "photos"
        self.out_dir = Path(out_dir)
        self._register_key()

    # ------------------------------------------------------------ clés
    def _register_key(self) -> None:
        """Enregistre la clé publique en base (utile au vérificateur et à la rotation)."""
        with self.Session() as s:
            if s.get(SigningKey, self.kid) is None:
                pem = self.private_key.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
                s.add(SigningKey(kid=self.kid, cle_publique=pem,
                                 cree_le=datetime.now(timezone.utc).isoformat(timespec="seconds")))
                audit.add_entry(s, self.operateur, "CLE_ENREGISTREE", self.kid)
                s.commit()

    # ------------------------------------------------------------ numérotation
    def next_card_id(self, profil: str, year: int | None = None) -> str:
        year = year or date.today().year
        prefix = f"{ID_PREFIX[profil]}-{year}-"
        with self.Session() as s:
            ids = s.scalars(select(Card.card_id).where(Card.card_id.like(f"{prefix}%"))).all()
        last = max((int(i.rsplit("-", 1)[1]) for i in ids), default=0)
        return f"{prefix}{last + 1:03d}"

    # ------------------------------------------------------------ construction
    def _fields(self, req: CardRequest, card_id: str, pic: Image.Image, today: date) -> dict:
        champs = {"kid": self.kid, "id": card_id, "nom": req.nom.strip().upper(), "prenom": req.prenom.strip(),
                  "naiss": req.naiss.isoformat(), "role": req.fonction.strip() if req.profil == "entreprise" else req.role.strip(),
                  "emis": today.isoformat(), "exp": _add_months(today, req.validite_mois).isoformat(),
                  "ph": photo.fingerprint(pic)}
        if req.profil == "entreprise":
            champs["svc"] = req.service.strip()
        return champs

    def build_card_data(self, req: CardRequest, card_id: str, signing_key: Ed25519PrivateKey | None = None,
                        today: date | None = None) -> tuple[CardData, dict]:
        """Construit la carte. signing_key permet un aperçu signé par une clé jetable."""
        today = today or date.today()
        pic = photo.normalize(req.photo_source)
        champs = self._fields(req, card_id, pic, today)
        token = sid_token.encode_token(champs, signing_key or self.private_key)
        data = CardData(prenom=champs["prenom"], nom=champs["nom"], card_id=card_id, role=req.role.strip(),
                        naiss=champs["naiss"], exp=champs["exp"], token=token, photo=pic, emis=champs["emis"],
                        fonction=req.fonction.strip(), service=req.service.strip(), profile=PROFILES[req.profil])
        return data, champs

    def preview(self, req: CardRequest) -> tuple[Image.Image, Image.Image]:
        """Aperçu non valable : signé par une clé jetable, rien n'est enregistré."""
        if req.photo_source is None:
            req.photo_source = Image.new("RGB", (600, 800), (226, 232, 240))
        card_id = self.next_card_id(req.profil) if req.profil in ID_PREFIX else "APERCU"
        data, _ = self.build_card_data(req, card_id, signing_key=Ed25519PrivateKey.generate())
        return render_card(data, req.modele)

    # ------------------------------------------------------------ émission
    def issue(self, req: CardRequest) -> Card:
        return self.issue_with_faces(req)[0]

    def issue_with_faces(self, req: CardRequest) -> tuple[Card, Image.Image, Image.Image]:
        """Émet la carte et renvoie aussi le recto et le verso (pour les planches d'impression)."""
        validate(req)
        card_id = self.next_card_id(req.profil)
        data, champs = self.build_card_data(req, card_id)
        recto, verso = render_card(data, req.modele)

        photo_path = photo.save(data.photo, self.photos_dir / f"{card_id}.png")
        pdf_path = export_card_pdf(recto, verso, self.out_dir / f"{card_id}.pdf",
                                   title=f"Carte {data.profile.org} - {card_id}")
        with self.Session() as s:
            holder = Holder(nom=champs["nom"], prenom=champs["prenom"], date_naissance=champs["naiss"],
                            role=data.role, etablissement=data.profile.org, fonction=data.fonction,
                            service=data.service, photo_path=str(photo_path), photo_hash=champs["ph"])
            s.add(holder)
            s.flush()
            card = Card(card_id=card_id, holder_id=holder.id, kid=self.kid, emis_le=champs["emis"],
                        expire_le=champs["exp"], token=data.token, statut="ACTIVE", profil=req.profil,
                        modele=req.modele, pdf_path=str(pdf_path))
            s.add(card)
            audit.add_entry(s, self.operateur, "EMISSION", card_id, f"{champs['prenom']} {champs['nom']}")
            s.commit()
            s.refresh(card)
            s.expunge(card)
        return card, recto, verso

    def render_existing(self, card_id: str) -> tuple[Image.Image, Image.Image]:
        """Redessine une carte déjà émise à partir de la base (jeton signé + photo enregistrée)."""
        with self.Session() as s:
            card = s.get(Card, card_id)
            if card is None:
                raise ValidationError(f"Carte {card_id} introuvable.")
            h = card.holder
            pic = Image.open(h.photo_path).convert("RGB") if h.photo_path and Path(h.photo_path).exists() \
                else Image.new("RGB", photo.PHOTO_SIZE, (226, 232, 240))
            data = CardData(prenom=h.prenom, nom=h.nom, card_id=card.card_id, role=h.role, naiss=h.date_naissance,
                            exp=card.expire_le, token=card.token, photo=photo.normalize(pic), emis=card.emis_le,
                            fonction=h.fonction or "", service=h.service or "", profile=PROFILES[card.profil])
            modele = card.modele
        return render_card(data, modele)

    # ------------------------------------------------------------ consultation
    def list_cards(self, search: str = "") -> list[dict]:
        with self.Session() as s:
            q = select(Card, Holder).join(Holder).order_by(Card.emis_le.desc(), Card.card_id.desc())
            if search.strip():
                like = f"%{search.strip()}%"
                q = q.where(or_(Card.card_id.ilike(like), Holder.nom.ilike(like), Holder.prenom.ilike(like)))
            return [{"card_id": c.card_id, "nom": h.nom, "prenom": h.prenom, "profil": c.profil,
                     "emis": c.emis_le, "exp": c.expire_le, "statut": c.statut, "pdf": c.pdf_path}
                    for c, h in s.execute(q).all()]

    # ------------------------------------------------------------ révocation
    def revoke(self, card_id: str, motif: str) -> None:
        if not motif.strip():
            raise ValidationError("Le motif de révocation est obligatoire.")
        with self.Session() as s:
            card = s.get(Card, card_id)
            if card is None:
                raise ValidationError(f"Carte {card_id} introuvable.")
            if card.statut == "REVOQUEE":
                raise ValidationError(f"La carte {card_id} est déjà révoquée.")
            card.statut = "REVOQUEE"
            s.add(Revocation(card_id=card_id, date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             motif=motif.strip(), operateur=self.operateur))
            audit.add_entry(s, self.operateur, "REVOCATION", card_id, motif.strip())
            s.commit()

    def export_for_verifier(self, folder: str | Path = "verif") -> Path:
        """Prépare le dossier de confiance du vérificateur : clé publique + liste de révocation signée."""
        folder = Path(folder)
        (folder / "cles").mkdir(parents=True, exist_ok=True)
        pem = self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        (folder / "cles" / f"{self.kid}_public.pem").write_bytes(pem)
        with self.Session() as s:
            ids = list(s.scalars(select(Card.card_id).where(Card.statut == "REVOQUEE")))
            rl = revocation.write(folder / "revocations.sid", ids, self.private_key, self.kid)
            audit.add_entry(s, self.operateur, "EXPORT_REVOCATIONS", str(folder), f"{len(ids)} carte(s)")
            s.commit()
        return rl

    def check_audit(self) -> audit.ChainReport:
        with self.Session() as s:
            return audit.verify_chain(s)
