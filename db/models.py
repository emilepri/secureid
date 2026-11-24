"""Tables de la base SecureID (SQLAlchemy 2)."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Holder(Base):
    """Titulaire d'une carte."""

    __tablename__ = "holders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(80))
    prenom: Mapped[str] = mapped_column(String(80))
    date_naissance: Mapped[str] = mapped_column(String(10))  # AAAA-MM-JJ
    role: Mapped[str] = mapped_column(String(40))
    etablissement: Mapped[str] = mapped_column(String(120))
    fonction: Mapped[str] = mapped_column(String(80), default="")
    service: Mapped[str] = mapped_column(String(80), default="")
    photo_path: Mapped[str | None] = mapped_column(String(255))
    photo_hash: Mapped[str | None] = mapped_column(String(64))

    cards: Mapped[list["Card"]] = relationship(back_populates="holder")


class Card(Base):
    """Carte émise : le jeton signé est conservé tel quel."""

    __tablename__ = "cards"

    card_id: Mapped[str] = mapped_column(String(40), primary_key=True)  # ex. STU-2026-001
    holder_id: Mapped[int] = mapped_column(ForeignKey("holders.id"))
    kid: Mapped[str] = mapped_column(String(40))
    emis_le: Mapped[str] = mapped_column(String(10))
    expire_le: Mapped[str] = mapped_column(String(10))
    token: Mapped[str] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE | REVOQUEE
    profil: Mapped[str] = mapped_column(String(20), default="ecole")    # ecole | entreprise
    modele: Mapped[str] = mapped_column(String(20), default="officiel")
    pdf_path: Mapped[str | None] = mapped_column(String(255))

    holder: Mapped[Holder] = relationship(back_populates="cards")


class Revocation(Base):
    __tablename__ = "revocations"

    card_id: Mapped[str] = mapped_column(ForeignKey("cards.card_id"), primary_key=True)
    date: Mapped[str] = mapped_column(String(25))
    motif: Mapped[str] = mapped_column(String(200))
    operateur: Mapped[str] = mapped_column(String(80))


class SigningKey(Base):
    """Clés publiques connues (la clé privée n'est jamais en base)."""

    __tablename__ = "keys"

    kid: Mapped[str] = mapped_column(String(40), primary_key=True)
    cle_publique: Mapped[str] = mapped_column(Text)  # PEM
    cree_le: Mapped[str] = mapped_column(String(25))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    """Journal chaîné : chaque ligne contient le hash de la précédente."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    horodatage: Mapped[str] = mapped_column(String(25))  # ISO 8601 UTC
    operateur: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    cible: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(Text, default="")
    hash_precedent: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
