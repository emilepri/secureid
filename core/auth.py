"""Comptes opérateurs : création, connexion, verrouillage, rôles.

- Mots de passe hachés avec Argon2id (jamais stockés en clair).
- Verrouillage du compte 5 minutes après 5 échecs consécutifs (anti force brute).
- Message d'erreur identique pour « compte inconnu » et « mauvais mot de passe »,
  pour ne pas révéler quels identifiants existent.
- Chaque connexion, échec, déconnexion et changement de compte est inscrit au journal d'audit.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from core import audit
from db.models import Operator

ROLES = {"admin": "Administrateur", "operateur": "Opérateur"}
MAX_ECHECS = 5
DUREE_VERROU = timedelta(minutes=5)
LOGIN_RE = re.compile(r"^[a-z0-9._-]{3,40}$")
GENERIC_ERROR = "Identifiant ou mot de passe incorrect."

_hasher = PasswordHasher()  # Argon2id, paramètres recommandés par la bibliothèque
# Hash factice : on fait le même calcul quand le compte n'existe pas (temps de réponse constant)
_DUMMY_HASH = _hasher.hash("compte-inexistant-secureid")


class AuthError(ValueError):
    """Erreur affichable telle quelle à l'utilisateur."""


@dataclass(frozen=True)
class CurrentUser:
    id: int
    login: str
    nom_complet: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def label(self) -> str:
        return f"{self.nom_complet or self.login} ({ROLES[self.role]})"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def check_password_policy(password: str, login: str = "") -> None:
    errors = []
    if len(password) < 12:
        errors.append("au moins 12 caractères")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errors.append("des lettres et au moins un chiffre")
    if login and login.lower() in password.lower():
        errors.append("ne pas contenir l'identifiant")
    if errors:
        raise AuthError("Le mot de passe doit contenir " + ", ".join(errors) + ".")


class AuthService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.Session = session_factory

    # ------------------------------------------------------------ comptes
    def has_operators(self) -> bool:
        with self.Session() as s:
            return s.scalar(select(func.count(Operator.id))) > 0

    def create_operator(self, login: str, password: str, role: str = "operateur",
                        nom_complet: str = "", created_by: str = "systeme") -> CurrentUser:
        login = login.strip().lower()
        if not LOGIN_RE.match(login):
            raise AuthError("Identifiant : 3 à 40 caractères parmi a-z, 0-9, point, tiret, souligné.")
        if role not in ROLES:
            raise AuthError("Rôle inconnu.")
        check_password_policy(password, login)
        with self.Session() as s:
            if s.scalar(select(Operator).where(Operator.login == login)):
                raise AuthError(f"L'identifiant « {login} » existe déjà.")
            op = Operator(login=login, nom_complet=nom_complet.strip(), hash_argon2=_hasher.hash(password),
                          role=role, actif=True, cree_le=_now().isoformat(timespec="seconds"))
            s.add(op)
            audit.add_entry(s, created_by, "COMPTE_CREE", login, ROLES[role])
            s.commit()
            return CurrentUser(op.id, op.login, op.nom_complet, op.role)

    def list_operators(self) -> list[dict]:
        with self.Session() as s:
            return [{"login": o.login, "nom": o.nom_complet, "role": o.role, "actif": o.actif,
                     "derniere": o.derniere_connexion, "verrouille": self._is_locked(o)}
                    for o in s.scalars(select(Operator).order_by(Operator.login))]

    def set_active(self, login: str, actif: bool, by: CurrentUser) -> None:
        with self.Session() as s:
            op = self._get(s, login)
            if op.login == by.login and not actif:
                raise AuthError("Tu ne peux pas désactiver ton propre compte.")
            if not actif and op.role == "admin" and self._active_admins(s) <= 1:
                raise AuthError("Impossible : il doit rester au moins un administrateur actif.")
            op.actif = actif
            op.echecs, op.verrouille_jusqu = 0, None
            audit.add_entry(s, by.login, "COMPTE_ACTIVE" if actif else "COMPTE_DESACTIVE", login)
            s.commit()

    def reset_password(self, login: str, new_password: str, by: CurrentUser) -> None:
        with self.Session() as s:
            op = self._get(s, login)
            check_password_policy(new_password, op.login)
            op.hash_argon2 = _hasher.hash(new_password)
            op.echecs, op.verrouille_jusqu = 0, None
            audit.add_entry(s, by.login, "MDP_REINITIALISE", login)
            s.commit()

    def change_own_password(self, user: CurrentUser, old: str, new: str) -> None:
        with self.Session() as s:
            op = self._get(s, user.login)
            try:
                _hasher.verify(op.hash_argon2, old)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                raise AuthError("Ancien mot de passe incorrect.") from None
            check_password_policy(new, op.login)
            op.hash_argon2 = _hasher.hash(new)
            audit.add_entry(s, user.login, "MDP_CHANGE", user.login)
            s.commit()

    # ------------------------------------------------------------ connexion
    def authenticate(self, login: str, password: str) -> CurrentUser:
        login = login.strip().lower()
        with self.Session() as s:
            op = s.scalar(select(Operator).where(Operator.login == login))
            if op is None:
                try:
                    _hasher.verify(_DUMMY_HASH, password)
                except VerificationError:
                    pass
                audit.add_entry(s, login or "?", "CONNEXION_ECHEC", login or "?", "compte inconnu")
                s.commit()
                raise AuthError(GENERIC_ERROR)

            if self._is_locked(op):
                audit.add_entry(s, login, "CONNEXION_REFUSEE", login, "compte verrouillé")
                s.commit()
                raise AuthError("Compte temporairement verrouillé après plusieurs échecs. Réessaie dans quelques minutes.")
            if not op.actif:
                audit.add_entry(s, login, "CONNEXION_REFUSEE", login, "compte désactivé")
                s.commit()
                raise AuthError("Ce compte est désactivé. Contacte un administrateur.")

            try:
                _hasher.verify(op.hash_argon2, password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                op.echecs += 1
                detail = f"échec {op.echecs}/{MAX_ECHECS}"
                if op.echecs >= MAX_ECHECS:
                    op.verrouille_jusqu = (_now() + DUREE_VERROU).isoformat(timespec="seconds")
                    op.echecs = 0
                    detail = "verrouillage 5 minutes"
                audit.add_entry(s, login, "CONNEXION_ECHEC", login, detail)
                s.commit()
                raise AuthError(GENERIC_ERROR) from None

            if _hasher.check_needs_rehash(op.hash_argon2):
                op.hash_argon2 = _hasher.hash(password)
            op.echecs, op.verrouille_jusqu = 0, None
            op.derniere_connexion = _now().isoformat(timespec="seconds")
            audit.add_entry(s, login, "CONNEXION", login)
            s.commit()
            return CurrentUser(op.id, op.login, op.nom_complet, op.role)

    def logout(self, user: CurrentUser, reason: str = "") -> None:
        with self.Session() as s:
            audit.add_entry(s, user.login, "DECONNEXION", user.login, reason)
            s.commit()

    # ------------------------------------------------------------ outils
    @staticmethod
    def _is_locked(op: Operator) -> bool:
        return bool(op.verrouille_jusqu) and datetime.fromisoformat(op.verrouille_jusqu) > _now()

    @staticmethod
    def _active_admins(s: Session) -> int:
        return s.scalar(select(func.count(Operator.id)).where(Operator.role == "admin", Operator.actif.is_(True)))

    @staticmethod
    def _get(s: Session, login: str) -> Operator:
        op = s.scalar(select(Operator).where(Operator.login == login))
        if op is None:
            raise AuthError(f"Compte « {login} » introuvable.")
        return op
