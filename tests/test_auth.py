from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from core.auth import MAX_ECHECS, AuthError, AuthService, check_password_policy
from core.audit import verify_chain
from db.database import get_engine, init_db
from db.models import AuditLog, Operator

MDP = "Teranga-2026-ok"


@pytest.fixture
def auth(tmp_path):
    return AuthService(init_db(get_engine(tmp_path / "t.db")))


def test_premier_admin_et_connexion(auth):
    assert not auth.has_operators()
    auth.create_operator("e.priso", MDP, "admin", "Emile PRISO")
    assert auth.has_operators()
    user = auth.authenticate("E.Priso ", MDP)  # casse et espaces tolérés
    assert user.is_admin and user.login == "e.priso"


def test_mot_de_passe_jamais_en_clair(auth):
    auth.create_operator("agent1", MDP)
    with auth.Session() as s:
        h = s.scalar(select(Operator.hash_argon2))
    assert MDP not in h and h.startswith("$argon2id$")


@pytest.mark.parametrize("mdp", ["court1", "sanschiffreaucun", "123456789012", "agent1-Secret-2026"])
def test_politique_mot_de_passe(mdp):
    with pytest.raises(AuthError):
        check_password_policy(mdp, "agent1")


def test_message_identique_compte_inconnu_ou_mauvais_mdp(auth):
    auth.create_operator("agent1", MDP)
    with pytest.raises(AuthError) as a:
        auth.authenticate("agent1", "mauvais-mdp-123")
    with pytest.raises(AuthError) as b:
        auth.authenticate("personne", "mauvais-mdp-123")
    assert str(a.value) == str(b.value)


def test_verrouillage_apres_echecs(auth):
    auth.create_operator("agent1", MDP)
    for _ in range(MAX_ECHECS):
        with pytest.raises(AuthError):
            auth.authenticate("agent1", "mauvais-mdp-123")
    with pytest.raises(AuthError, match="verrouillé"):
        auth.authenticate("agent1", MDP)  # même le bon mot de passe est refusé
    # Le verrou expire
    with auth.Session() as s:
        op = s.scalar(select(Operator))
        op.verrouille_jusqu = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        s.commit()
    assert auth.authenticate("agent1", MDP).login == "agent1"


def test_compte_desactive(auth):
    admin = auth.create_operator("admin1", MDP, "admin")
    auth.create_operator("agent1", MDP)
    auth.set_active("agent1", False, admin)
    with pytest.raises(AuthError, match="désactivé"):
        auth.authenticate("agent1", MDP)
    auth.set_active("agent1", True, admin)
    assert auth.authenticate("agent1", MDP)


def test_dernier_admin_protege(auth):
    admin = auth.create_operator("admin1", MDP, "admin")
    with pytest.raises(AuthError):
        auth.set_active("admin1", False, admin)


def test_identifiant_unique_et_valide(auth):
    auth.create_operator("agent1", MDP)
    with pytest.raises(AuthError, match="existe"):
        auth.create_operator("AGENT1", MDP)
    with pytest.raises(AuthError):
        auth.create_operator("a b", MDP)


def test_changement_et_reinitialisation(auth):
    admin = auth.create_operator("admin1", MDP, "admin")
    user = auth.create_operator("agent1", MDP)
    auth.change_own_password(user, MDP, "Nouveau-mdp-2027")
    assert auth.authenticate("agent1", "Nouveau-mdp-2027")
    auth.reset_password("agent1", "Reinit-mdp-2028", admin)
    assert auth.authenticate("agent1", "Reinit-mdp-2028")


def test_tout_est_audite(auth):
    auth.create_operator("agent1", MDP)
    user = auth.authenticate("agent1", MDP)
    with pytest.raises(AuthError):
        auth.authenticate("agent1", "faux-mdp-1234")
    auth.logout(user, "manuelle")
    with auth.Session() as s:
        actions = s.scalars(select(AuditLog.action).order_by(AuditLog.id)).all()
        assert actions == ["COMPTE_CREE", "CONNEXION", "CONNEXION_ECHEC", "DECONNEXION"]
        assert verify_chain(s).ok
